package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.Serializable;
import java.util.Arrays;
import java.util.Iterator;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Modifier;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;

public class CSVRecord_11_1Test {

    private Constructor<CSVRecord> constructor;

    @BeforeEach
    public void setUp() throws Exception {
        constructor = CSVRecord.class.getDeclaredConstructor(String[].class, Map.class, String.class, long.class);
        constructor.setAccessible(true);
    }

    @Test
    @Timeout(8000)
    public void testSize_withNonEmptyValues() throws Exception {
        String[] values = new String[] { "a", "b", "c" };
        Map<String, Integer> mapping = Mockito.mock(Map.class);
        CSVRecord record = constructor.newInstance((Object) values, mapping, "comment", 1L);

        int size = record.size();

        assertEquals(3, size);
    }

    @Test
    @Timeout(8000)
    public void testSize_withEmptyValues() throws Exception {
        String[] values = new String[0];
        Map<String, Integer> mapping = Mockito.mock(Map.class);
        CSVRecord record = constructor.newInstance((Object) values, mapping, null, 0L);

        int size = record.size();

        assertEquals(0, size);
    }

    @Test
    @Timeout(8000)
    public void testSize_withNullValuesField() throws Exception {
        // Create instance with non-null values first
        String[] values = new String[] { "x" };
        Map<String, Integer> mapping = Mockito.mock(Map.class);
        CSVRecord record = constructor.newInstance((Object) values, mapping, null, 0L);

        // Use reflection to set private final values field to null
        Field valuesField = CSVRecord.class.getDeclaredField("values");
        valuesField.setAccessible(true);

        // Remove final modifier for the field (works on Java 8 and later)
        Field modifiersField = Field.class.getDeclaredField("modifiers");
        modifiersField.setAccessible(true);
        modifiersField.setInt(valuesField, valuesField.getModifiers() & ~Modifier.FINAL);

        valuesField.set(record, null);

        // Expect NullPointerException when size() is called because values is null
        try {
            record.size();
        } catch (NullPointerException e) {
            // expected
            return;
        }
        throw new AssertionError("Expected NullPointerException when values is null");
    }
}