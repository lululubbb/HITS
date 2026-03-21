package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.Serializable;
import java.util.Arrays;
import java.util.Iterator;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.fail;
import static org.mockito.Mockito.mock;

import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Modifier;
import java.util.Map;

import org.apache.commons.csv.CSVRecord;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

public class CSVRecord_11_5Test {

    private Constructor<CSVRecord> constructor;

    @BeforeEach
    public void setUp() throws Exception {
        constructor = CSVRecord.class.getDeclaredConstructor(String[].class, Map.class, String.class, long.class);
        constructor.setAccessible(true);
    }

    @Test
    @Timeout(8000)
    public void testSize_withNonEmptyValues() throws Exception {
        String[] values = new String[] {"a", "b", "c"};
        Map<String, Integer> mapping = mock(Map.class);
        String comment = "comment";
        long recordNumber = 1L;

        CSVRecord record = constructor.newInstance((Object) values, mapping, comment, recordNumber);

        int size = record.size();

        assertEquals(3, size);
    }

    @Test
    @Timeout(8000)
    public void testSize_withEmptyValues() throws Exception {
        String[] values = new String[0];
        Map<String, Integer> mapping = mock(Map.class);
        String comment = null;
        long recordNumber = 0L;

        CSVRecord record = constructor.newInstance((Object) values, mapping, comment, recordNumber);

        int size = record.size();

        assertEquals(0, size);
    }

    @Test
    @Timeout(8000)
    public void testSize_withNullValuesFieldUsingReflection() throws Exception {
        String[] values = new String[] {"x"};
        Map<String, Integer> mapping = mock(Map.class);
        String comment = "test";
        long recordNumber = 5L;

        CSVRecord record = constructor.newInstance((Object) values, mapping, comment, recordNumber);

        // Set the private final field 'values' to null using reflection to test behavior
        Field valuesField = CSVRecord.class.getDeclaredField("values");
        valuesField.setAccessible(true);

        // Remove final modifier from the field 'values'
        Field modifiersField = Field.class.getDeclaredField("modifiers");
        modifiersField.setAccessible(true);
        modifiersField.setInt(valuesField, valuesField.getModifiers() & ~Modifier.FINAL);

        valuesField.set(record, null);

        // Since values is null, calling size() will cause NullPointerException.
        // We catch it here to verify.
        try {
            record.size();
            fail("Expected NullPointerException when values is null");
        } catch (NullPointerException e) {
            // expected
        }
    }
}