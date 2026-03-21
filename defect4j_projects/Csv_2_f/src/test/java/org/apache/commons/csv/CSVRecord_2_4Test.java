package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.Serializable;
import java.util.Arrays;
import java.util.Iterator;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.util.Collections;
import java.util.HashMap;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

public class CSVRecord_2_4Test {

    private CSVRecord csvRecord;
    private String[] values;
    private Map<String, Integer> mapping;

    @BeforeEach
    public void setUp() {
        values = new String[] { "value0", "value1", "value2" };
        mapping = new HashMap<>();
        mapping.put("col0", 0);
        mapping.put("col1", 1);
        mapping.put("col2", 2);
        csvRecord = new CSVRecord(values, mapping, "comment", 123L);
    }

    @Test
    @Timeout(8000)
    public void testGetByIndex_ValidIndexes() {
        assertEquals("value0", csvRecord.get(0));
        assertEquals("value1", csvRecord.get(1));
        assertEquals("value2", csvRecord.get(2));
    }

    @Test
    @Timeout(8000)
    public void testGetByIndex_IndexOutOfBounds_Negative() {
        assertThrows(ArrayIndexOutOfBoundsException.class, () -> csvRecord.get(-1));
    }

    @Test
    @Timeout(8000)
    public void testGetByIndex_IndexOutOfBounds_TooLarge() {
        assertThrows(ArrayIndexOutOfBoundsException.class, () -> csvRecord.get(values.length));
    }

    @Test
    @Timeout(8000)
    public void testGetByIndex_UsingReflection() throws Exception {
        Method getMethod = CSVRecord.class.getDeclaredMethod("get", int.class);
        getMethod.setAccessible(true);

        assertEquals("value0", getMethod.invoke(csvRecord, 0));
        assertEquals("value1", getMethod.invoke(csvRecord, 1));
        assertEquals("value2", getMethod.invoke(csvRecord, 2));
    }

    @Test
    @Timeout(8000)
    public void testGetByIndex_Reflection_IndexOutOfBounds() throws Exception {
        Method getMethod = CSVRecord.class.getDeclaredMethod("get", int.class);
        getMethod.setAccessible(true);

        InvocationTargetException thrown1 = assertThrows(InvocationTargetException.class, () -> getMethod.invoke(csvRecord, -1));
        assertEquals(ArrayIndexOutOfBoundsException.class, thrown1.getCause().getClass());

        InvocationTargetException thrown2 = assertThrows(InvocationTargetException.class, () -> getMethod.invoke(csvRecord, values.length));
        assertEquals(ArrayIndexOutOfBoundsException.class, thrown2.getCause().getClass());
    }

    @Test
    @Timeout(8000)
    public void testGetByIndex_EmptyValuesArray() {
        CSVRecord emptyRecord = new CSVRecord(new String[0], Collections.emptyMap(), null, 0L);
        assertThrows(ArrayIndexOutOfBoundsException.class, () -> emptyRecord.get(0));
    }
}