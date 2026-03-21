package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.Serializable;
import java.util.Arrays;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Modifier;
import java.util.Iterator;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

public class CSVRecord_7_1Test {

    private CSVRecord csvRecord;
    private String[] values;
    private Map<String, Integer> mapping;
    private String comment;
    private long recordNumber;

    @BeforeEach
    public void setUp() throws Exception {
        values = new String[] { "value1", "value2", "value3" };
        mapping = mock(Map.class);
        comment = "comment";
        recordNumber = 123L;

        Constructor<CSVRecord> constructor = CSVRecord.class.getDeclaredConstructor(String[].class, Map.class, String.class, long.class);
        constructor.setAccessible(true);
        csvRecord = constructor.newInstance(values, mapping, comment, recordNumber);
    }

    @Test
    @Timeout(8000)
    public void testIterator() {
        Iterator<String> iterator = csvRecord.iterator();
        assertNotNull(iterator);

        int index = 0;
        while (iterator.hasNext()) {
            assertEquals(values[index], iterator.next());
            index++;
        }
        assertEquals(values.length, index);
    }

    @Test
    @Timeout(8000)
    public void testIteratorEmptyValues() throws Exception {
        // Create CSVRecord with empty values array
        Constructor<CSVRecord> constructor = CSVRecord.class.getDeclaredConstructor(String[].class, Map.class, String.class, long.class);
        constructor.setAccessible(true);
        CSVRecord emptyRecord = constructor.newInstance(new String[0], mapping, comment, recordNumber);

        Iterator<String> iterator = emptyRecord.iterator();
        assertNotNull(iterator);
        assertFalse(iterator.hasNext());
    }

    @Test
    @Timeout(8000)
    public void testIteratorValuesNull() throws Exception {
        // Use reflection to set private final field values to null to test behavior
        Field valuesField = CSVRecord.class.getDeclaredField("values");
        valuesField.setAccessible(true);

        // Remove final modifier on 'values' field
        Field modifiersField = Field.class.getDeclaredField("modifiers");
        modifiersField.setAccessible(true);
        modifiersField.setInt(valuesField, valuesField.getModifiers() & ~Modifier.FINAL);

        valuesField.set(csvRecord, null);

        // iterator() will throw NullPointerException because Arrays.asList(null) throws NPE
        assertThrows(NullPointerException.class, () -> {
            csvRecord.iterator();
        });
    }
}